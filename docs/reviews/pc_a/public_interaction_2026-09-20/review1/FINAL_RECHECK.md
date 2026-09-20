# Round-1 reviewer: fixed-source repair recheck

Fixed source: `b391400d7272510067cd5b1173843077cb92091c`. HEAD verified before/after; worktree clean at final inspection. This is the first reviewer's repair verification, not a substitute for the separately requested second independent reviewer.

Disposition: the previously reported P2 positional-join defect is fixed. No remaining blocking defect identified in the bounded component scope reviewed. This does not accept the complete natural P5 loop.

## Executed evidence

- Original `repro.py` now completes both current and restored delayed-prefix derived evidence. Its final deliberately forged `CALIBRATED_CONTACT` association now raises `ValueError: invalid geometric association status`, so that original script exits nonzero for the now-correct rejection (fixed-repro.log).
- Independently constructed a source with media times arriving in reverse order (0.5 then 0.0) and real import timestamps 30 seconds apart. Inference succeeds, derived evidence follows original observation IDs, interactions sort media time to 0.0/0.5, and legal restore preserves exactly identical derived evidence. The runtime no longer bases this archive's association gaps on inference wall-clock delay.
- Seven independent damaged-checkpoint cases rejected with the previously live checkpoint unchanged: stale receipt, negative time with recomputed receipt, wrong visual media time, wrong visual archive identity, wrong crop dimensions, duplicate JSON key, and wrong observation ID. Script/log: timeline_recheck.py / timeline_recheck.log.
- Six affected existing test modules: **92 passed, 0 failures, 0 errors, 0 skipped**, recorded in recheck.xml / recheck-tests.log. This is a separate review subset, not to be added to the parent's overlapping regression total.
- Code inspection confirms video records now read associations and hand-object evidence from the same producer; the external association track was removed.

## Remaining interpretation limits

Archive receipt checks bind declared media sampling, RGB payload, crop dimensions and observation identity while preserving actual import wall-clock timestamps. These timestamps remain explicitly a resampling grid, not original exposure timestamps. A fully consistent caller-authored replacement receipt is not cryptographic proof of origin or author truth. Author-aligned object poses are evaluator-only; geometric measurements do not become calibrated contact/role probabilities or semantic transitions. Full-LFS authenticity verification is still explicitly absent. None of this establishes delayed semantic correction, executed environment action, B-side acceptance or scientific benefit.
