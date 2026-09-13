# Independent person-evidence review, round 1

Source fixed at `cf81e207de29971981ce6eafd845e1599a32de23` in `/private/tmp/cpswm-pc-a-person-evidence-20260914`. Production files read only. Independent scripts `probe.py` and `crop_probe.py` with their `.out` outputs retained.

## Findings requiring repair

1. **P2: visual causal time validation accepts invalid timestamps.** `CausalInstanceAssociator._update` directly compares datetime values. Independent probe accepts naive timestamps, and accepts `America/New_York` 2025-11-02 01:30 fold=1 capture followed by fold=0 arrival/cutoff: capture is actually 3600 seconds later than arrival. Normalize aware datetimes to UTC before order comparison and reject naive timestamps. Validate before any state mutation, then verify legal retry.
2. **P2: requested crop can differ from actual pixels while receipt claims the requested crop.** `run_person_interaction_video.py` uses FFmpeg `crop=w:h:x:y` without exact cropping. On actual provided HOH `01.mp4` (846x200, yuv420p), `crop=100:100:1:0` gives exactly the same 30000 output bytes as `crop=100:100:0:0`, and differs from `crop=100:100:1:0:exact=1`. Default chroma subsampling rounds the odd horizontal offset. The receipt/sequence hash therefore states x=1 while the detector sees x=0. Use exact cropping or convert to RGB before cropping; independently test non-chroma-aligned origins and dimensions. The attached real-video probe asserts the mismatch and retains all three SHA256 values.

## Scope observations

- Source MP4 digest is checked and the verified bytes are copied to the decoder temporary file, avoiding source-file reopen substitution.
- Media timestamps are explicitly resampling grid times, while envelope timestamps are import acquisition times; they are not claimed original camera exposure timestamps.
- Current association is same-class geometric matching. The new/ambiguous branch and gap termination are conservative but do not establish persistent household identity, calibrated association probability or reidentification.
- Role alternatives are box-overlap candidates, not contact/release evidence or identified transfer roles. Memory authority remains false. Changing a request string is not robot execution.
- Calibration is an algorithm over caller-supplied labels. The stated annotation source/digests are not independent authentication; no independently annotated real fit/heldout set or empirical calibration improvement is established by these files. Sequence/input separation is only as sound as those supplied identities.
- The producer deliberately withholds semantic transition authority and verifies no core change. That abstention is appropriate, but it cannot establish the user's complete real-input/action/revision loop.

Repair both P2 findings before scoped acceptance; final verification must bind to the same final source used by round two. This review is diagnostic frontend coverage only, not full-axis/P5, long-term memory promotion, actual robot actions, complete task acceptance or scientific benefit.

## Final-source re-verification and calibration CLI review

Verified fixed source **`6f142dbf732009a82e08cd882b62f55708dfdd6d`**, with independent `final_probe.py` and `final_probe.out`; original failed probes remain untouched.

- Naive time and the original DST reversed-time case now raise ValueError. For each rejection a subsequent valid frame on the same tracker succeeds, confirming rejection does not consume the observation or mutate association state.
- The production filter explicitly contains `exact=1`. Running that same filter shape on the real HOH video now distinguishes x=1 from x=0; an odd-origin, odd-size 101x99 crop yields exactly 101*99*3 bytes. Both original P2 findings are fixed within this scope.
- Independently exercised the newly added annotation loader: five predictions with only four labels produce exactly four examples (the unlabeled prediction is not a negative). Changed observation IDs and changed cropped-pixel hashes from the **same source video** remain blocked as fit/holdout leakage. A separate-source synthetic math fixture passes evaluation. None of these labels constitute empirical real-video calibration evidence.
- Reviewed loader annotation digest/provenance requirement, candidate-ID join, duplicate/unmatched annotation rejection and model/weight/library/filter signature binding. Source/video hashes and annotation provenance remain caller-supplied integrity identifiers, not independent truth authentication. The CLI's new source hash checks are explicitly bounded disk-source checks, not all-runtime execution attestation.

No additional reproducible blocking issue found in this limited final-source review. Sign-off is restricted to these frontend/crop/time/calibration-input checks. No real independent annotation set, calibrated real role evidence, semantic promotion, robot action or full task completion is established.
