# Fixed-source independent component review, round 1

Reviewed commit: `34fa9b3c81d3ffd83beeb3d6d6dde88107578f2f`; comparison base `78c5a8f`. HEAD verified before and after. Review was read-only in the worktree. Synthetic tests below are boundary checks, not natural capability evidence. No final five-task acceptance is granted.

## Finding requiring repair

**P2 — join source histories by identity, not tuple position** (`src/cpswm/perception_mapping/natural_vision.py:468-472`). `_frames` and `_hand_frames` preserve admitted prefix order, but `_recompute_interactions` groups by camera and sorts by capture time. For a legitimate delayed frame (capture t−0.5, arrival t+1 after an already-admitted frame at t), both `infer` calls succeed; `hand_object_evidence()` then raises `ValueError: hand/object measurements require the same source frame`. The same failure occurs after successful checkpoint restore. This blocks exactly the delayed evidence use case; multiple cameras can trigger the same mismatch. Join unique observation IDs, reject missing/duplicate coverage, and preserve explicit output ordering. Reproducer: `repro.py`, output `repro.log`.

## Verification performed

- Existing five affected test modules: 81 passed, exit 0 (tests.log). Modules: core4d_range_reader, hand_object_evidence, natural_hands, natural_vision, interaction_evidence.
- Independently generated 900,123 random bytes split into five uneven parts including a 1-byte part. 400 random seek/read requests, whole-stream read, and fully cached replay with network forbidden all matched. Total downloaded bytes 900,123. See range_probe.py/log.
- Existing positive ZIP cross-part extraction/cached replay, budget exhaustion, changed cache, wrong archive identity, short response, source mismatch and forged box tests passed.
- Legal delayed-source inference and restore reproduced the failure above without mutating production internals.

## Trust and measurement limits

1. Downloader validates exact ranges, ZIP CRC, byte count and cached SHA digests; it explicitly does not verify full LFS object hashes. Replacing both cache bytes and their stored digest is accepted by the range reader (reproduced), so these hashes establish local integrity under a trusted cache, not cryptographic author authenticity. ZIP CRC adds accidental corruption checking, not author authentication. No full-author-authenticity claim should be added.
2. A caller can retain a visual hash/candidates and forge association track IDs or status text. `measure_hand_object_evidence` copies the status (reproduced with `CALIBRATED_CONTACT`), while the top-level result remains `IMAGE_GEOMETRY_ONLY_CONTACT_ROLE_AND_POSE_UNRESOLVED`. Production producer recomputes associations and restore compares derived results, which protects its normal path. The standalone helper is not an authenticator of complete hand/model/association claims. Restricting status vocabulary would harden this interface; external generated claims must not be promoted based on this helper alone.
3. Image landmark-to-box distance and wrist containment remain image geometry. Ambiguity is retained; no role/contact probability is manufactured. Pixel overlap cannot establish contact, release or world pose; missing measurements do not prove absence.
4. `run_person_interaction_video` separately computes associations using resampled media time. The producer's own associations use capture time, which this importer fills with wall-clock import time. If inference exceeds the 1-second association gap, producer and exported external associations can differ. This timing distinction predates the patch but matters when interpreting the new same-producer derived API: exported record counts do not independently prove the producer has identical associations.
5. Label-stratified CORE4D development selection is disclosed, and author sequence labels are stored in a separate evaluator directory. This is not independent frame-event supervision or a held-out evaluation.
6. The real two-person extraction/inference was running in the parent task; I did not claim or validate its unfinished artifacts. Fixed-source code and synthetic boundary tests do not establish a real P5 semantic transition, reversible semantic correction, changed executed action, or scientific benefit.

Disposition: component repair required for P2 before round 2. Broader natural-loop acceptance remains open.
