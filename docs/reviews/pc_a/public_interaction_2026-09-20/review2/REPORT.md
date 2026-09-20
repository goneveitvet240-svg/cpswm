# Independent fixed-source component review, round 2

Reviewed `b391400d7272510067cd5b1173843077cb92091c`, comparison base `78c5a8f`. HEAD verified before and after; no source files edited. Parent task's untracked report directory appeared during review and is not reviewed production code. This review follows the first review's late-frame positional-join defect; it is a component review, not acceptance of the full five-task natural loop.

## Disposition

No blocking component defect found in this round. The first review's positional pairing defect is repaired: derived evidence joins unique observation identities and rejects missing/duplicate coverage. The same-producer association clock now uses validated archive sampling time instead of inference/import wall time. Unknown/ambiguous image geometry remains distinct from role/contact probability and metric pose.

## Independent verification

- Six affected modules: **92 passed**, 0 failed, 0 skipped; `tests.log`, `tests.xml`. Modules: core4d_range_reader, hand_object_evidence, archive_media_timeline, natural_hands, natural_vision, interaction_evidence.
- Independently constructed six incremental prefixes mixing two cameras, late archive frames and 30-second import gaps. Every prefix returned hand/object records in the input observation-ID order and exactly matched reconstructed-producer checkpoint restoration (`probe.py`, `probe.log`).
- Changed archive time and recomputed its receipt while retaining old derived checkpoint records: restore rejected atomically with original state unchanged. Transplanting a complete receipt to another observation ID was rejected. Forged `CALIBRATED_CONTACT` association status was rejected.
- Independently built a 1.5 MB random-content ZIP across four uneven parts (including a one-byte part), interrupted fetch on the fourth range, then resumed. Three cached blocks were retained, six new ranges fetched, extracted payload matched exactly, and fully cached replay succeeded with all network fetches forbidden (`range_resume.py`, `range_resume.log`).
- Verified all ten acquired evaluator-only author files against manifest length, SHA256 and ZIP CRC. Both object pose arrays loaded with `allow_pickle=False` and were finite. This verifies local receipt consistency, not author event truth or calibrated natural model performance (`supervision.log`). Code reads selected pose/alignment metadata only into the separate evaluator directory and does not load human-motion pickle or feed author poses to the inference runner.

## Explicit limits

1. Range hashes and CRC establish local consistency under trusted cache/metadata. Full archive LFS hashes remain unverified, correctly disclosed. Complete replacement of bytes plus local digests is not authenticated by these checks.
2. Archive sampling receipts bind source declaration, observation ID, RGB payload, crop, FPS and resampled time. A coherently re-authored new receipt with a different valid media time is accepted (independently demonstrated). This is a trusted-importer boundary, not proof against fabricated original-video provenance. The runner pins and decodes source bytes; callers cannot claim that receipt validation alone re-derives original exposures. Resampled grid times are explicitly not original exposure times.
3. The standalone hand/object geometry helper is not a cryptographic authenticator of model results. The normal producer path recomputes associations and validates restored derivations. Pixel distance, overlapping person boxes and detector scores remain uncalibrated geometry; they cannot establish contact, release, ordered role, world identity or 6D pose.
4. Label-stratified public development selection is disclosed. Sequence action names and author object poses do not supply independent per-frame hand-contact/release/correction labels. No held-out scientific benefit is established.
5. Network-interruption resume was verified. Arbitrary process termination between cache `.bin` and `.sha256` writes is not covered; a partial cache pair can fail closed and require cache repair. No durable transactional-download guarantee is granted.
6. Real new crop inference was running in the parent task and was not evaluated here. Prior 17-frame run with zero detected hands is a preserved failure, not natural hand evidence. Neither these tests nor this review establish a natural P5 semantic transition, reversible semantic memory correction, changed executed action, full-loop acceptance or B-machine independent validation.

Scope: repaired source/time association and download/evaluator/geometry boundary components accepted for continued development, with the above limits. Complete project acceptance remains open.
