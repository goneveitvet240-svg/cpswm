# Independent review 2 — evaluator-only supervision audit

Initial source: `a9ea12aa7f234a84a57539bdc47ffea734b16ea4`. Review performed independently of review 1; production code was not modified by this reviewer. This is an A-side component review, not B reproduction or natural P5 acceptance.

## Initial findings requiring repair

1. **P2 — temporal leakage in per-frame edge support.** `boundary_support` applied SciPy Sobel directly to `[T,H,W]`; its smoothing includes the time axis. With three black RGB frames and a rectangular mask, placing a white rectangle in frame 0 produced scores `[6.2966678798, 6.2966678798, 0]`; frame 1 remained entirely black. Thus changing a neighboring frame changes a fixed frame's claimed RGB/mask support. Compute spatial gradients independently per RGB frame and rerun exploratory scores.
2. **P2 — floating-point audit output contract.** `pose_audit` accepted all floating dtypes, but float16 and longdouble identity transforms raised `TypeError` in NumPy linalg. A finite float64 matrix with `rotation[0,0]=1e308` returned an infinite orthogonality residual; the CLI's `allow_nan=False` then cannot serialize the diagnostic. None of these cases falsely passed rigidity, but the audit failed to return a usable result. Define supported arithmetic and preserve explicit overflow/nonfinite diagnostics without changing author arrays.

## Independent checks at initial SHA

- `python -m pytest -q tests/test_supervision_alignment.py`: 12 passed, zero failed/skipped.
- Executed the full pinned CLI independently, output `/private/tmp/cpswm-review2-alignment-a9ea12a`; source SHA/hashes checked by the runner. Dataset revision `81bb2bb876a4a54ac94e67c788d7c31364f1c43e`.
- Sequence 023: 260 decoded RGB frames; 60 masks of 1080×1920; table 180×6; 180 poses, no rigid-transform defects at tolerance 1e-5.
- Sequence 024: 294 decoded RGB frames; 70 masks; table 208×6; 208 poses, seven rigid-transform defects at rows 130, 131, 132, 133, 136, 180, 181.
- Values 0,1,2,3 observed; value 3 appears in 27/60 and 38/70 masks respectively. No person/object identity was assigned to these values. Absence of a mask value was not treated as physical absence.
- Both outputs keep `accepted_frame_links=[]`, `identity_labels=[]`, `event_labels=[]`, `usable_for_role_or_contact_calibration=false`, and status `UNVERIFIED_ALIGNMENT`; summary reports zero semantic transitions.
- Source reference search found this module called only by the evaluator CLI and tests, with no natural producer/P5/memory/action connection.
- Existing tests cover timestamp ordering/count/integer precision, malformed transform rows, unverified index hypotheses, empty/translated edge observations, pinned bytes, allocation limits and object-array rejection. Fractional table cells are rejected by the installed NumPy parser.

## Acceptance boundary

Matching table/pose lengths, finite matrices, larger edge-support scores and the presence of mask IDs do not establish frame alignment, identity, contact, release, actor roles, calibrated pose error or scientific benefit. The published six-column table still differs from the reported current seven-column author generator. No accepted frame mapping or role supervision exists. The full natural P5 correction/action/recovery loop remains outside this component.

Final fixed-source recheck: pending repair SHA; initial exploratory edge scores must not be retained as final results.

## Final fixed-source recheck

Rechecked `3534e9796bb2aae99b594a330671a1328ddf5ccf` independently. Both initial P2 findings are resolved within this component's stated contract.

- `python -m pytest -q tests/test_supervision_alignment.py`: **18 passed**, zero failed/skipped. This count includes the original 12 and six regression cases; it must not be added to another review's overlapping test count.
- Independently reran the original temporal-leakage example: scores now `[6.2966678798, 0, 0]`; unchanged black neighboring frames stay unsupported.
- Independently tested float16/float32/float64/longdouble identity transforms and confirmed they pass without mutating inputs. The finite `1e308` transform is rejected as non-rigid with `FLOAT64_COMPUTATION_OVERFLOW`, and its result serializes with `allow_nan=False`.
- Read the complete production diff: Sobel now runs on each two-dimensional image separately; numerical diagnostics use float64 and explicitly record overflow; ffmpeg uses `-fps_mode passthrough`.
- Independently reran both real sequences through the complete pinned CLI at the final SHA; output `/private/tmp/cpswm-review2-alignment-3534e97`. The source binding in its summary is the final SHA. RGB/mask/pose counts and seven invalid 024 pose rows remain as reported above.
- Final edge matrices are 60×260 and 70×294. Exploratory candidate means (row-equal, three-times-row, table-column candidate) are respectively **1.916843 / 3.357643 / 3.733782** for 023 and **2.519465 / 3.510889 / 4.059970** for 024. These replace all initial edge scores; they remain non-probabilistic diagnostics and do not choose an accepted mapping.
- Final outputs still contain zero accepted frame links, zero event/identity labels and zero semantic transitions. Component result: engineering diagnostics pass the reviewed checks, alignment remains unverified, natural closed loop and scientific gain are not established, B review is not performed by this reviewer.

No remaining blocking finding in the reviewed component. This conclusion is bound to the final SHA and does not certify unsupported cases beyond the checks described above.
