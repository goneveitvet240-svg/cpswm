# Independent natural vision review round 1

Fixed source audited: `9d50afb79fdba2e854edddb2f5ec1179e071604c`, worktree `/private/tmp/cpswm-pc-a-natural-vision-20260914`. Production source was read only. Independent executable probe and full output: `probe.py`, `probe.out`; synthetic archive and output retained alongside them.

## Blocking component findings

1. **P2 — CLI source identity comes from unrelated working directory.** `tools/run_natural_vision_archive.py` invokes `git rev-parse HEAD` and `git status` without binding cwd to its repository. The probe invokes the real CLI and official detector from a separate clean Git repository. Output claims source `e9e7f472568edc73862c424596dc9f92dc1729a8` and `git_dirty=false`, while the actual audited source is `9d50afb79fdba2e854edddb2f5ec1179e071604c`. This is a supported invocation (absolute script/archive paths) and materially mislabels evidence. Bind Git to the script repository and disable replace refs. Also distinguish post-run source hashes from a source execution freeze: the current after-inference hashes alone do not establish no source changed during execution.

2. **P2 — duplicate capture identity silently overwrites source receipt.** The `captures = {row["capture_ref"]: row ...}` comprehension accepts duplicate capture refs. A fully hashed manifest containing two `capture1` entries with receipt hashes `aaaa...` and `bbbb...` is accepted, runs the actual official detector successfully, and silently emits `bbbb...` as the frame receipt. Reject ambiguous duplicate identities before inference instead of selecting last-wins. Validate observation identities across archive entries too; distinct filenames must not imply distinct observations. This test does not claim an independently trusted digest was subverted: it shows that correctly hash-pinned but internally ambiguous archives pass as coherent input.

## Actual model and wire observations

- The independent probe really instantiates the production detector, loads the local pinned official SSDlite state dict and executes an inference on synthetic zero-valued 4x4 RGB pixels. No model mock is used; runtime records torch `2.13.0` and torchvision `0.28.0`, yielding zero candidates at 0.5.
- Weight bytes are hashed once and exactly those bytes are passed through BytesIO to `torch.load(weights_only=True, map_location="cpu")` and strict state-dict load, avoiding weight-path reopen TOCTOU. `weights=None, weights_backbone=None` avoids implicit download. Eval/inference mode and disabled gradients are explicit.
- Archive payloads are retained as checked bytes and inference consumes those checked bytes, limiting payload reopen TOCTOU. Manifest capture references remain the identity defect above.
- RGB allocation bounds, dtype/shape/exact byte length, hash, scope and capture/arrival cutoff checks are explicit. Arrival timestamps in this offline archive are replay timestamps, not proof of current transport custody.
- The detector score is correctly labelled uncalibrated, empty detections do not authorize absence, and categories do not become identities, roles or pose.

## Scope

Repair the two identity findings before accepting the CLI evidence path. This is a natural-appearance pixel candidate frontend only. It is not a calibrated GroundedTransition producer, persistent instance association, multi-person role inference, full-axis/P5 assembly or a physical-action closed loop. Even after repairs, this bounded review cannot sign the user's complete unified runtime acceptance or scientific superiority. The retained probe uses synthetic pixels, so it is actual model-loading evidence, not real-world detection accuracy evidence.

## Final-source re-verification

Bound to fixed SHA `a3d1ea6de4db1d1bf9038482abbbefbdf707880c`. Original `probe.py` and failure output are retained unchanged. Independent `final_probe.py` / `final_probe.out` now verify:

1. The original duplicate-capture manifest is rejected with `duplicate capture reference`.
2. After removing that ambiguity, invoking the actual official-weight detector CLI from the same unrelated Git cwd records the correct audited repository SHA. Output reports `source_unchanged=true`, and explicitly limits source identity to entry/detector files rather than all runtime execution. The model runs on the synthetic frame; the continuous entry records zero semantic transitions, zero physical actions and unchanged core state.
3. An additional fully hashed archive with distinct filenames but the same observation identity is rejected with `duplicate observation identity`.

All three independent assertion groups passed; both original P2 findings are closed for this fixed source. The new producer's broader behavior is reserved to the second independent reviewer; this verification does not claim complete new-producer coverage. In particular, successful pixel inference plus deliberate abstention still does not establish calibrated semantics, persistent identity, P5 or the requested complete action/revision loop.

## Shared final source after second-round repair

Re-executed the three independent assertion groups against **`6bb72386d588c82f0e264afa1dadd51306c1cada`** after the second review's JSON/NPY capture-ref pairing repair. `closure_probe.py` preserves the prior probe logic with a new exact SHA assertion and distinct artifact paths; `closure_probe.out` retains the new actual-model run. Duplicate capture reference rejection, correct source SHA from foreign cwd, and duplicate observation rejection all pass. The legal run again records zero semantic transitions/physical actions and unchanged core state. Original and intermediate evidence remain untouched. This is the final source binding for round one's limited frontend evidence-path acceptance; all earlier limits remain, and pairing-specific adversarial coverage belongs to the second reviewer.
