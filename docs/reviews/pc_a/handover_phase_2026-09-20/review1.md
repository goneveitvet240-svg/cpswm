# Independent review 1 — phase supervision component

Reviewed fixed source `12ea3c5fda771b80ede285c18b36450adbf419b0`, base `9eaaa56`. Production code was not edited. This is a component audit, not B acceptance or natural P5 acceptance.

## Independent verification

- `.venv/bin/python -m pytest tests/test_handover_phase_supervision.py -q`: 15 passed, no failed/skipped.
- Independent real-data run of `tools/inspect_bimanual_phase_subset.py` with manifest SHA `621626525ee58468394943b35cd638f8bb7b622f09deffe448a5304f0e0c2f37`; output `/private/tmp/cpswm-review1-phase-independent-20260920/phase-references.json` explicitly binds the reviewed SHA.
- Four clips, six valid videos, 290 decoded frames. Camera 2 in clips 1 and 2 is `INVALID_ALL_ZERO` and contributes zero decoded frames/references. Clip 1 camera 1 and clip 3 both cameras each have one outside-author-range frame, explicitly unknown rather than extrapolated.
- Read the acquired author ReadMe. Filename order does identify giver then receiver; participants in trajectory column names are checked against that pair. The author's phase definition uses hand distance within 20 cm of minimum and relative speed below 15 cm/s, so these are motion-threshold proxies, not independently verified physical contact/release labels.
- CSV hashes, timeline monotonicity, exact-row behavior, two-label transition brackets, explicit unknown/out-of-range states and unresolved visual identity bindings are appropriately retained. Partial ZIP extraction does not establish the archive MD5; manifest records this limitation.

## Findings requiring follow-up

1. **P2 — cross-member identity is not enforced by the inspector.** Phase sequence is derived from `receipt.member`, but camera and depth records are selected only by `local_path`. A newly generated/modified manifest containing two valid camera payloads swapped between opaque clip paths (with correct size/hash receipts) would be accepted with the wrong phase sequence. Pinning the original manifest protects this exact run, but does not validate identity consistency when accepting a new manifest. Check exact author member paths against expected pair, sequence and camera; add legal-file swap rejection tests.
2. **Model-input gate:** the parent discovered burned-in Reach/Transfer/Retreat text in the author videos. The reviewed component is evaluator-only and no model run is claimed. These published RGB files must not be admitted directly as clean model observations. Any fixed crop must be source-bound and verified across both cameras; crop success alone does not establish human identity or physical contact ground truth.

Conclusion: the exact original-manifest evaluator run is reproducible and honestly scoped. Defer approval of a reusable acquisition/model-input boundary until cross-member binding and overlay exclusion are reviewed on the new fixed SHA. No calibrated contact/role likelihood, runtime semantic transition, memory correction, or P5 action was established by this component.

## Fixed-source follow-up — 5188e65986eab9f6345ec03231968858296bd8aa

Independently reviewed the updated source without reading the other reviewer report. First-round finding 1 is closed: `validate_member_pairing` enforces exact sequence, participant-pair directory, camera directory and corresponding depth filename; the swapped legitimate-member test rejects wrong camera and reversed role sequence.

- Re-ran `tests/test_handover_phase_supervision.py`: **22 passed**, no failed/skipped. This replaces the earlier 15-test count; counts overlap and must not be added.
- Re-ran the real evaluator with the same pinned manifest into `/private/tmp/cpswm-review1-phase-final-20260920`; output binds full fixed SHA `5188e65986eab9f6345ec03231968858296bd8aa`, again 4 clips / 6 valid videos / 290 frames.
- Independently called the new runtime allowlist validator on all six real approved videos. All pass exact source hash, byte count and 1920×1080 dimension checks. Both all-zero camera-2 files are rejected.
- Independently decoded the first frame of each of the six videos both full-size and with `crop=1920:960:0:0:exact=1`; all six cropped byte arrays exactly equal the upper 960 rows of their full RGB array. This checks pixel routing, not human annotation accuracy or every-frame visual content.
- The dedicated frontend reads the fixed pixel policy, not author phase tables, acquisition manifest, or role mapping. It forces the crop; the underlying replay runner verifies the expected source digest again and decodes a frozen copy of those verified bytes. Its observations carry source digest, crop and cropped payload digest. The wrapper adds source-file/policy hashes and binds the resulting JSON digest.
- The allowlist itself has only opaque clip paths, video hashes/sizes and fixed geometry. It supplies no giver/receiver or phase answers. Original videos remain author-labeled artifacts; direct use of the generic replay tool with another crop is not authorized by this wrapper's receipt. Parent visual inspection across both cameras is the evidence for bottom-strip placement; my six-frame byte check independently verifies that the specified strip is removed.

Final scoped conclusion: **no outstanding blocking finding in the reviewed evaluator and fixed six-video pixel-entry component**. This does not independently validate model detections, phase accuracy, visual-person identity binding, contact likelihood calibration, B acceptance, or a natural P5 action/recovery loop. Physical-contact truth remains absent and synchronization remains nominal with no measured error bound. Any later production source change requires renewed review.
