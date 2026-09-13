# Natural vision second independent review

Frozen source: `a3d1ea6de4db1d1bf9038482abbbefbdf707880c`, worktree `/private/tmp/cpswm-pc-a-natural-vision-20260914`.

## Changes requested: P2 inconsistent paired capture references accepted

The CLI pairs JSON with its same-stem NPY file, checks both bytes against manifest hashes, but ignores the NPY entry's capture_ref. In a copy of the real four-view 512 archive, changing only the first RGB NPY capture_ref from `000000.json` to `000001.json` while retaining the JSON capture_ref and recomputing the supplied manifest digest is accepted by the actual detector CLI. It emits the JSON row's receipt as though the pair had coherent capture attribution. The archive is internally contradictory despite every payload hash being correct. Reject different or unknown paired capture references before inference.

Executable independent reproduction: `probe_cli.py`; `cli_stdout.txt`, `mismatched_output/summary.json`, `mismatched_output/frames.json`. Actual pinned weights were loaded and actual inference ran: four RGB frames, eight raw observations, one potted-plant candidate, zero semantic transitions/actions, unchanged core. This is not a claim to defeat an independently trusted manifest hash; it is a failure to reject an internally inconsistent but completely hashed manifest, analogous to the first-round duplicate-reference finding.

## Passing independent checks

- Actual CLI invoked with foreign cwd `/private/tmp` records the correct source SHA, verifying the first source-binding P2 repair.
- Duplicate captures entries reject before inference/output creation, verifying the first duplicate-reference P2 repair (`duplicate_stdout.txt`).
- Six independently authored pytest probes passed in 0.67 s (`test_independent.py`, `stdout.txt`, `junit.xml`). Synthetic helper construction is reused, attack sequences/assertions are independent.
- A valid first frame followed by bad hash, mismatched scope, future arrival, duplicate identity, or oracle channel commits neither prefix nor frames; valid retry succeeds.
- Failure on the detector's second call leaves frames/prefix/cutoff uncommitted; retry succeeds. Returned frame mutation does not alias retained evidence.

## Limits

Source reporting explicitly covers entry and detector files, not full runtime execution attestation. Capture receipt hashes supplied in the archive are dependency labels, not independent authenticity/calibration proof. Trusted detector/backend replacement and forged internally coherent input are not excluded by this boundary. The frontend returns uncalibrated candidates and None, withholding semantic transitions. It does not establish instance/person roles/pose, trained calibrated evidence, full P5 assembly, or a complete physical-action/retraction loop. Neither positive plant detection nor zero detections establishes those capabilities.

## Final frozen-source verification

Final SHA: `6bb72386d588c82f0e264afa1dadd51306c1cada`.

The paired capture-reference defect is repaired before output creation or inference. Independent final CLI checks (`final_verify.py`, `final_cli_checks.json`, `final_*.txt`) pass all six scenarios: original mismatched paired references, unknown reference, duplicate capture reference, orphaned pair, mismatched optional observation identity all reject before output directory creation; the legal four-view 512 archive runs the actual pinned detector from foreign cwd successfully. Its summary binds the correct final source SHA, records four frames/eight raw observations, verifies unchanged core, and reports zero semantic transitions and physical actions. Original failed-source archive and successful contradictory output remain retained separately.

The unchanged six independent producer atomicity/alias probes also pass on final SHA in 0.70 s (`final_stdout.txt`, `final_junit.xml`).

Verdict: no unresolved blocking issue found in the inspected and independently exercised candidate-frontend/archive consistency paths after repair. This scoped second review does not constitute whole-runtime attestation, calibrated semantic grounding, complete real-input action/retraction acceptance, or a scientific benefit claim. Original scope limitations remain.
