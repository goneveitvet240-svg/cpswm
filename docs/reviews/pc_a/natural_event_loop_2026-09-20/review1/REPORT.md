# Independent component review, round 1

Reviewed commit: `c8fe8d5152c6713f889a19aee4f4756dfa1de49c`; base: `769a558bc3deb2c4133f509722a748fa37bdc990`.
Scope: natural event coverage, window download changes, pinned pixel hand detector, optional hand input and durable recovery. This is NOT acceptance of the complete natural P5 loop, five-task delivery, or scientific benefit.

## Findings

### P2 — restore silently loses hand evidence and admits contradictory frame bindings

`src/cpswm/perception_mapping/natural_vision.py:349-364` validates only the top-level hand model binding and then accepts `state.get("hand_frames", ())`. In a hand-enabled checkpoint with one already-consumed RGB observation, removing `hand_frames` succeeds; subsequent inference on the identical prefix leaves 1 visual frame and 0 hand frames forever because the prefix has already advanced. A HandFrame with a different observation UUID and different model binding is also accepted as long as the top-level binding remains correct. Thus the advertised checkpoint model binding does not bind the actual restored evidence.

Reproduction: `.venv/bin/python /private/tmp/cpswm-natural-review1/repro_checkpoint.py` from the reviewed worktree. Output:

```
missing key accepted; visual/hand frames= 1 0
wrong observation and model accepted= True
failed restore changed state= True
```

Require the hand field for hand-enabled state and validate count, order, raw observation identity, capture time, payload and receipt hashes, dimensions, and per-frame model binding against retained RGB/visual evidence before committing. When hands are disabled, reject any restored hand evidence. This is a malformed or mixed-checkpoint acceptance issue; no claim is made that ordinary successful checkpoint serialization spontaneously corrupts data.

### P2 — failed restore mutates live producer state

`natural_vision.py:360-364` assigns interactions before reading all mandatory fields. With valid top-level bindings but missing `frames`, `restore_state` changes interactions and then raises KeyError. The producer after rejection differs from its pre-restore checkpoint. This assignment order predates the patch, but the new hand restore expands the same non-atomic restore path, and remains relevant to the requested recovery acceptance.

Same reproduction above. Validate and deepcopy all fields into local variables first, then make one all-or-nothing commit. Tests should compare the entire prior state after each malformed-state rejection.

## Independent executions

- Existing bounded tests: `tests/test_natural_hands.py` and `tests/test_natural_event_coverage.py`: 17 passed. Covers legal raw hand fixture path, inference failure/retry atomicity, candidate validation, pinned-weight rejection, SQLite roundtrip, missing hand sentinel, missing object pose, finite validation, noncontiguous endpoint motion remaining unresolved.
- Independently ran the CLI with locally calculated source manifest/receipt pins on both real datasets (`run_coverage.py`). 180 original and 360 additional frames pass hash and pairing checks. Output directories contain full frame inventories and pose-pair diagnostics. These local pins validate consistency with the retained files, not an independent author signature.
- Deliberate explicit annotation-member swap with regenerated annotation-manifest pin is rejected before output (`repro_pairing.py`: `annotation is paired to another frame`). Original datasets were not modified.
- Source review: raw adapter excludes author labels; hand inference accepts raw RGB only; detector binds official artifact SHA256 before importing/loading MediaPipe. Returned model-local metric coordinates are not published as measured world poses. Hand scores are explicitly uncalibrated; hands are not exported as actor/contact evidence.
- Window logic uses metadata-derived prefix/midpoint/suffix indices and deduplicates overlap. This review did not re-download remote archives or independently test network-server range behavior.

## Coverage limits

The actual downloaded files have no explicit pickup, move, release, interperson-handoff or correction event labels. Author pose displacement is an endpoint diagnostic only. One subject's two hands do not establish two people. No natural semantic transition or physical action follows from these component checks. The running real MediaPipe 360-frame inference was not rerun or modified by this reviewer. Full synchronized forgery of all data/manifests/receipts against newly chosen trust pins is not ruled out by self-computed hashes. Independent author provenance and full natural closed-loop acceptance remain outside this review.

Verdict: component review requests fixes for restoration validation and atomicity; full natural P5 acceptance remains open.
