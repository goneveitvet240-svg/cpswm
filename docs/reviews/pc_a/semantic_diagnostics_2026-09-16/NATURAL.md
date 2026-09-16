# Natural RGB-D geometry: actual run, not a qualified semantic update

2026-09-16. Parent task source commit is recorded in the encompassing report. This
subtask's `output/natural-geometry-frozen/summary.json` binds the two changed runtime
files before and after its run; that limited binding is not full interpreter or
P5 source attestation.

## Implemented and executed

`natural_geometry.py` consumes actual raw RGB/depth wire observations and externally
pinned prior Faster R-CNN pixel predictions. It verifies RGB identities, raw payload
hashes, camera/sequence/capture pairing, exact acquisition receipts and causal cutoff.
It never opens author object IDs, segmentation labels, object poses or hand labels.
The existing visual inference was not rerun; this is recorded prediction replay plus
new geometric computation from actual depth pixels, not fresh detector inference.

The 180 paired inputs are admitted frame by frame through one existing
`ContinuousEvidenceInput` and a `NaturalGeometryProducer`. The latter retains its
source-bound candidates in the same stream's producer state. It does **not** insert
unqualified candidates into the core's `ConditionalMeasurement` history. Those two
histories must not be confused.

For every non-person box, integer pixel centres and positive aligned depth are
retained. The producer emits three actual observed surface points nearest depth
ranks 0.05/0.50/0.95, valid/missing pixel counts and depth spread. Ranks are descriptive
order statistics, not probabilities. Boxes may contain the target, hand, support
or room background; neither a depth median nor a box centre is labelled as an
object centre. The record explicitly retains unknown instance, orientation and
likelihood model, all `None`, and all ambiguity reasons. No detector score becomes
an identity or responsibility probability.

## Actual results

- 180 RGB-D pairs / 360 raw observations, one uninterrupted diagnostic stream.
- 413 non-person surface candidates; 412 contain valid depth; 1 explicitly has no
  valid depth. This is not object recall or semantic accuracy.
- 334 boxes have 5%–95% depth spread greater than 0.10 m. This is a descriptive
  foreground/background-mixing indicator, **not** a fitted error threshold or a
  calibrated rejection rule. No scientific gate is decided by this number.
- All 180 `advance` results are `INSUFFICIENT_SEMANTIC_EVIDENCE`.
- `GroundedTransition = 0`, accepted conditional measurements = 0, semantic memory
  updates = 0, environment actions = 0. The core snapshot remains unchanged.
- A separate six-real-frame interruption control persists the actual continuous
  stream to SQLite after each operation, closes after frame 3, reopens with
  `ContinuousEvidenceInput.resume`, and consumes frames 4–6. Its complete surface
  records equal the uninterrupted stream's first six frames. This is **six-frame
  candidate-state recovery**, not full semantic recovery or physical feedback.

## Camera source and coordinate limits

Camera: `105322251564`, image 640×480. Author calibration file SHA256:
`8f004a684c62c94bf21b3b2b0e103aa81e1cb7f315f2f307b2537695243509a8`.
Color intrinsic parameters are fx=378.30926513671875,
fy=378.024658203125, cx=323.66534423828125, cy=253.562744140625.
The existing HO-Cap raw import follows the author's aligned depth convention
(depth millimetres / 1000, color intrinsics). The tool consumes that explicit
assumption; it does not independently calibrate the RGB-depth alignment.

The pinhole coordinates are `(u-cx)*z/fx, (v-cy)*z/fy, z`, nominal camera x right,
y down and z forward. The author's nonzero distortion coefficients are retained
but not applied because the YAML does not itself establish a unique distortion
model/corrected-image convention. Therefore output fields say
`nominal_pinhole_xyz_m` and every candidate carries an uncorrected-distortion
warning. No world transform is applied. These values cannot currently be treated
as calibrated metric object position or full `C`.

## Exact legal-consumer gap

The full `C = position + orientation` scope is preserved. We inspected the actual
consumer rather than assuming every measurement must have six observed entries:

1. `structure_two_conditional_updates.py:30–48` defines generic measurement `z`,
   matrix `H`, covariance `R`, model/source IDs and information weight. Lines
   121–135 allow an `m × 6` matrix with `m=3`; a partial observation can mathematically
   update a six-dimensional state without inventing observed orientation. But it
   must have a meaningful measurement function, positive-definite calibrated
   residual covariance and independently sourced responsibility/weight. Pixel
   depth spread is not that residual covariance.
2. `pose_observation_model.py:48–63` specifically requires a complete `PoseState`
   pair; lines 128–139 fit full-rank 6D residual error from independent labels.
   `PoseConditionalHistory` lines 283–315 binds object/reference/epoch and uses
   a fixed 6×6 identity observation matrix. It is not a partial surface adapter.
3. `structure_two_pose.py:57–69,84–94` requires a physical instance, timestamp,
   coordinate frame and quaternion. A frame detection UUID cannot establish the
   object identity, and a nominal camera surface point is not an object pose.
4. `structure_two_continuous_input.py:63–75` `GroundedTransition` carries a
   `PrototypeTransition` and calibration ID. It also requires source-backed
   acquisition opportunity propensities; finding a box cannot manufacture those.

The smallest remaining contract work is an explicit partial-observation producer
for named/symmetry-aware object hypotheses: observed subspace or measurement
function, raw-source/epoch/camera-frame binding, occluder/background alternatives,
instance responsibility, an independently fitted and evaluated measurement error
model, and retraction of the corresponding history entry. That adapter can target
the existing general conditional updater while keeping unobserved orientation in
the state. It still needs a lawful transition/opportunity path into P5. Merely
padding the three-vector with zero orientation or adding identity covariance would
silently invent evidence, so this run rejects it.

## Verification and scope

`tests/test_natural_geometry.py`: 9 passed. Covers actual pixel projection,
multiple depth surfaces, missing depth, mismatched receipt/source/camera/future
cutoff/boxes, duplicate replay, truncation rejection and dependency-bound restore.
Ruff passes all three added Python files. Mypy passes the new source module.
The encompassing task may run broader tests; this is not an independent review.
The requested two whole-task adversarial rounds remain the parent task's duty.

Preserved raw manifest pin:
`2333b3202fa8dbffb56fa931f64a8156f61ec438954d06993b1cf7bbece66107`.
Preserved Faster frames pin:
`ffb6609d01552c9beb28b129d4fb395aa43b36a276e005ca1d9d5ea60ee69d7d`.
The actual summary and complete candidate records are copied to this report's
`evidence/natural_geometry_*` artifacts. No raw image or SQLite checkpoint is
included in Git.
