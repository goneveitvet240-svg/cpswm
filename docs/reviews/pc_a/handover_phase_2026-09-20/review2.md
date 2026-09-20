# Independent component review 2

Reviewed fixed source: `12ea3c5fda771b80ede285c18b36450adbf419b0`.
Fixed dataset manifest SHA-256: `621626525ee58468394943b35cd638f8bb7b622f09deffe448a5304f0e0c2f37`.
This review did not read review 1, modify production code, or commit. It is a local independent component review, not computer B acceptance or natural P5 validation.

## Findings requiring repair

1. **P2 — Depth CSV parser silently chooses an ambiguous clock or crashes on incomplete rows.** `tools/inspect_bimanual_phase_subset.py:101–114` uses permissive `csv.DictReader` without checking unique headers or exact row width. `Index,Time,Time\n0,9,0\n1,8,1\n` is reported as parsed with times 0 and 1, concealing the competing decreasing clock. Extra cells are also accepted. `Index,Time\n0\n` raises an uncaught TypeError instead of returning INVALID_TABLE. This does not authorize alignment (the flag remains false), but it weakens the claimed invalid-table audit and makes one malformed sidecar abort unrelated clip inspection. Require unique required columns, exact row widths and strict CSV syntax; normalize malformed-table failures.

2. **P2 — Unterminated author CSV quotes can pass phase acceptance.** `src/cpswm/data_preflight/handover_phase_supervision.py:63` uses the default non-strict csv.reader. A legal six-column header followed by `0,reach,reach,0,0,"1` without the closing quote parses into a valid AuthorPhaseSeries when its actual digest is supplied. The digest verifies bytes, not CSV validity. Use strict CSV parsing and reject malformed quoting. Existing row-width and source-digest checks do not cover this case. No evidence that the fixed acquired files contain this fault.

## Independent verification

- `.venv/bin/pytest -q tests/test_handover_phase_supervision.py`: **15 passed**.
- Independently invoked `tools/inspect_bimanual_phase_subset.py` on the manifest above; output is `/private/tmp/cpswm-phase-review2-independent-20260920/phase-references.json`.
- Four clips, eight acquired RGB members, **six successfully decoded videos / 290 total decoded frames**, two all-zero invalid MP4 members retained as invalid (both P07/P08 camera 2 directions).
- **760 author motion rows / 16 role-specific phase boundaries**. Frame references contain 287 giver AUTHOR_PROXY states and three OUTSIDE_AUTHOR_RANGE states. These are nominal projected references, not 287 verified physical events.
- Depth sidecars: one INVALID_NULL_BYTES; seven parsed clocks with no depth frames acquired and no alignment authorization. Negative initial offsets are preserved, consistent with timestamps relative to first RGB frame; they are not automatically treated as invalid absolute time.
- Actual excerpt counts: clip-0001 201 author rows / 51 decoded frames; clip-0002 177 / 45; clip-0003 201 / 102; clip-0004 181 / 92.
- Independently reproduced both findings with in-memory byte payloads and matching hashes; no production code modified.

## Semantic and isolation assessment

The author README explicitly defines role order in sequence names and describes annotations using hand-distance and relative-velocity thresholds. The code preserves giver and receiver separately, checks the participant set, flags visual identity UNRESOLVED, rejects nonfinite/nonmonotone motion times, preserves both adjacent phase labels at a nominal crossing and does not extrapolate past authored endpoints. Exact-row projection remains nominal: it does not establish RGB/mocap synchronization accuracy.

`contact_or_release_gold=False`, `runtime_evidence_authorized=False`, nominal synchronization with no measured error bound, and evaluator-only output are maintained. Source search found the parser/projection used by the inspection tool and tests, with no production perception/P5 consumer. Model-visible raw paths are opaque clip names; the manifest and evaluator outputs must continue to be withheld from runtime because they carry author sequence/role information.

The acquired fixed data and labels cannot establish person-to-image identity, calibrated contact/release, independent event truth, pose accuracy, posterior memory revision, changed physical actions, recovery equivalence or scientific benefit. Full archive MD5 is explicitly unverified; member CRC plus recorded hashes provide scoped integrity only. The depth and nominal phase clocks must not be promoted to calibrated alignment. Two parser findings must be repaired before accepting the strict invalid-input audit claim.

## Pixel-isolation follow-up on the same initial source

After notification of a suspected baked-in label, I independently decoded camera 1 clip-0001 at 0.7 seconds to `/private/tmp/cpswm-review2-bimanual-frame.png` and visually confirmed the bottom-center **Reach** text. Opaque filenames do not remove that label. No runtime inference was executed on these videos in this review. Original labeled video is acceptable as evaluator material only; a separately verified label-removal crop with provenance and fixed input rules is required before treating pixels as model-visible input. This is a blocking input-isolation requirement, not proof of a runtime leak already executed.

## Repair verification — fixed 5188e65986eab9f6345ec03231968858296bd8aa

Both CSV findings are **closed at this fixed source**. Author parsing now rejects malformed quoting; depth parsing requires unique required columns and exact row widths, uses strict CSV parsing and emits INVALID_TABLE for the reproduced malformed inputs. `.venv/bin/pytest -q tests/test_handover_phase_supervision.py` independently passed **22 tests**. An attempted separately named pixel test file did not exist and ran no tests; the actual pixel-policy test is included in those 22. No counts are added to the earlier 15 because coverage overlaps.

The real inspector was independently rerun to `/private/tmp/cpswm-phase-review2-fixed-5188e65/phase-references.json`: **four clips, six valid decoded videos, 290 frames**. The same two all-zero videos remain invalid. Nominal projection is still evaluator-only and explicitly marks published original pixels as burned-in-label material. The new member-pairing check rejects source sequence/camera mismatch.

The six actual videos independently passed `validate_pixel_input` against the checked-in policy SHA allowlist, byte lengths and original 1920×1080 dimensions. `run_bimanual_pixel_frontend.py` has no author-phase CSV or acquisition-manifest input; it hardcodes the crop `(0,0,1920,960)`, removing the entire 120-pixel bottom strip, and includes policy/source hashes and the resulting result.json digest in its receipt. The underlying video runner checks the expected source digest again, decodes a frozen copy of those verified bytes and applies the crop before observations are constructed. Policy changes/full-frame geometry and unknown inputs are rejected by the fixed entry path. This is entry-path isolation, not a sandbox preventing arbitrary other tools from opening original files.

I independently decoded clip-0003 camera-2 at 0.8 seconds with the exact fixed crop and visually inspected `/private/tmp/cpswm-review2-fixed-camera2-crop.png`: output is 1920×960, the lower phase banner is absent, and motion-capture markers remain. Initial camera-1 original-frame evidence is retained above. This spot check does not assert marker-free household input or exhaustively prove absence of every possible visual cue.

No remaining blocking issue found within the inspected parser, nominal proxy and fixed crop entry-path scope. Final model-run receipt verification is pending the run output; I have not independently rerun the neural models. Neither component repair nor cropped pixels establishes verified physical contact/release truth, resolved visual person IDs, calibrated synchronization, natural P5 transitions, closed-loop actions or B acceptance.

## Completed actual-output verification at the same fixed source

The four finished outputs under the main repository `output/handover-phase-20260920/pixels/clip-0001` through `clip-0004` were independently checked. Every result reports fixed source `5188e65986eab9f6345ec03231968858296bd8aa`. Every pixel-policy receipt matches the actual result.json SHA-256; every listed frontend/policy source hash matches the current fixed file; every input video matches the allowed source digest. The run reports git_dirty=true (review documents were being written); this is retained rather than represented as a clean whole-tree attestation. Listed source-file bindings pass, and the receipt explicitly limits attestation to entry/frontend files.

All **64 saved .npy inputs** were loaded with `allow_pickle=False`: uint8 shape **(960,1920,3)**, each file digest matches its per-frame receipt and visual input digest, crop is `(0,0,1920,960)`, and resampled media times are `index / 10`. For an independent pixel check, I decoded each ORIGINAL FULL video frame at fps=10, then cropped the top 960 rows in NumPy rather than reusing the production ffmpeg crop filter. **All 64 saved input arrays match those independently decoded-and-cropped pixels exactly.** Check summary: `/private/tmp/cpswm-review2-pixel-receipts-5188e65.json`. No neural inference was rerun in this check.

Observed counts from verified result files:

| Clip | Sampled frames | Raw regional hand candidates | Hand-object measurements | Uncalibrated ordered role alternatives | Memory writes | Executed actions |
|---|---:|---:|---:|---:|---:|---:|
| 0001 | 17 | 5 | 46 | 5 | 0 | 0 |
| 0002 | 15 | 5 | 46 | 3 | 0 | 0 |
| 0003 | 17 | 25 | 446 | 17 | 0 | 0 |
| 0004 | 15 | 23 | 373 | 15 | 0 | 0 |
| Total | 64 | 58 | 911 | 40 | 0 | 0 |

The 58 candidates may duplicate physical hands across overlapping regions; 911 geometric measurement records and 40 ordered role alternatives are neither independent identities nor calibrated contact/role truth. Final scoped disposition: parser repairs and fixed crop/source/output binding **verified**, no remaining blocking finding in that component scope. Full natural P5 closure, scientific gain and computer B review remain unverified.
