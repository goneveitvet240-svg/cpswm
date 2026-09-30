# Next bounded task: original archive RGB-D → controlled native position consumer

2026-10-01. **Design only.** No bridge implementation, archive inference,
training, Unity execution, or native bridge acceptance was performed for this
document. This is not R1/R2. The existing synthetic native consumer tests and the
real archive's numeric diagnostic remain separate evidence until this bridge is
implemented, frozen, reviewed and executed.

## Purpose and boundary

Use one predeclared original archive RGB-D packet as the actual raw input to the
controlled position producer. Keep the original envelope, identities, receipt
and payload bytes intact. Construct a separate, explicitly synthetic semantic
fixture whose scope matches that packet and whose semantic timeline follows its
capture/arrival. Matching scope is an interface construction; it does not make
the synthetic object, actors, locations, events or identity association true of
the photographed scene.

This supplies a useful next engineering consequence: an archived public
measurement, rederived from its originals, changes actual native likelihood,
weights and conditional statistics, survives SQLite recovery, and disappears
when its bound semantic source is withdrawn. It still does not solve natural
instance association, unknown/clutter calibration, formal position-reference
selection, orientation observation or camera-action utility.

## Existing entry points

Repository-relative paths below are in
`/private/tmp/cpswm-pc-a-soft-position-factor-20261001`:

- `tools/run_correction_replay_comparison.py`: `build`, `ingest`,
  `apply_feedback`, `OracleProducer`, `raw_for`.
- `tests/structure_two_backbone_wiring_probe.py`: `BackboneWiringProbe.build`,
  `observed_days`, `transition_for`, `_opportunity`, `ciav_input`,
  `router_features`.
- `src/cpswm/system/evaluation_operations/structure_two_action_death_test.py`:
  `VisibleActionCase`, `ActionDayObservation`,
  `StructureTwoActionScenarioGenerator`.
- `tools/controlled_position_producer.py`: `packet_binding`,
  `ControlledPositionProducer`.
- `src/cpswm/system/native_neural_production.py`: `NeuralNativeProducer`.
- `src/cpswm/system/structure_two_continuous_input.py`:
  `ContinuousEvidenceInput.admit`, `produce_joint_posterior`,
  `replay_joint_posterior`, `resume`.
- `tests/test_native_position_production.py`: `scenario`, `advance`,
  `fresh_joint`, and the withdrawal/replay/SQLite comparison.

Do **not** call the existing `run_correction_replay_comparison.build` unchanged:
it constructs a new fixed-date probe with another scope internally. Reuse its
small stream/store/context-builder assembly with the already adapted probe.
The scenario generator currently fixes its initial time to 2026-01-01 and derives
its scope from its controlled seed; it has no archive-scope/time arguments.

## Original packet: immutable fields

Load the selected packet through the already pinned original capture archive and
its existing verification path. Retain the original offline command and delivery
as external provenance. Check the source inventory/pins before selecting a frame.

For every `RawModalityObservation`, keep these fields unchanged:

- `envelope_json` (the original string, not a new serialization);
- `payload_bytes`;
- `capture_receipt_sha256`;
- `archive_sampling_json`;
- `depth_unit`.

Consequently all original observation, metadata-record, payload and action UUIDs,
both envelope scope locations (`identity` and `metadata`), source identifiers,
capture/arrival/recorded times, sensor and coordinate-frame declarations, camera
parameters, payload hashes and worker/Unity/house/configuration pins remain intact.
Assert original equality and the `packet_binding` digest before and after use.
Do not edit camera self-pose or image time to fit the old synthetic scenario.

The original offline command is **not** a command issued by the new continuous
runtime. Do not insert it into `_observation_commands`, `_observation_status` or
native-origin tables. Do not call `execute_observation` to pretend the archived
delivery is a newly executed camera action. Do not create a
`NativeVisualAuthority` proof for this archive admission. Use
`NeuralNativeProducer(..., use_owned_visual_context=False)`; the controlled
candidate reads the admitted originals from `context.visible_prefix`.

## Exact controlled-fixture construction

1. Obtain `S = (household_id, session_id, trace_id)` from the selected RGB
   envelope's `identity`. Verify all three original channels have that scope and
   share the validated action/capture pairing. Obtain the original delivery and
   all envelope capture/arrival timestamps.
2. Create the ordinary controlled probe, for example
   `old_probe = BackboneWiringProbe.build(seed=171)`. Keep its fixture actors,
   object UUID, location UUIDs, priors, evidence likelihood parameters, policy,
   utility and initial system unchanged. Do not substitute SDK object IDs or
   private target coordinates.
3. Define a deterministic synthetic time anchor:
   `T = max(delivery.received_at, all capture times, all arrival times) + 1 second`.
   Let `delta = T - old_probe.observed_days()[0].before.detection_time`.
   This makes even the first synthetic before-record follow original arrival.
   A single delta preserves all synthetic time gaps and event ordering.
4. Rebuild **all** case days, including optional actor/mechanism/role evidence,
   instead of fixing only the selected after-record. Change only synthetic
   records. For each non-None before/after/evidence record:
   - start with `record.model_dump(mode="python")`;
   - copy its metadata dictionary and set household/session/trace to `S`;
   - add `delta` to `metadata.recorded_time`;
   - add `delta` to non-None `detection_time` or `evidence_time`, as applicable;
   - optionally label synthetic `metadata.source_id`/`model_version` explicitly
     as the controlled archive bridge (do not alter the archive's metadata);
   - reconstruct with `type(record).model_validate(updated_dict)`.
5. Reconstruct each `ActionDayObservation` from its updated nested records with
   `type(day).model_validate(...)`; then rebuild the complete visible case with
   `VisibleActionCase.model_validate({...old_case.model_dump(mode="python"),
   "days": rebuilt_days})`. `model_copy(update=...)` alone does not validate
   nested updates and is insufficient as the final step.
6. Construct `probe = BackboneWiringProbe(case=new_case,
   system=old_probe.system)` before that system consumes any records. Keep
   `step_index` at its initial value. Serialize/pin this adapted visible case and
   the deterministic construction rule before native execution.

For this one-packet, one-store fixture, retain the generator's synthetic record
UUIDs. This also retains valid `observation_opportunity_id`,
`source_detection_result_id`, `object_instance_id` and `evidence_cluster_id`
references without an incomplete UUID rewrite. These UUIDs are fixture identities,
not SDK identities. Use separate stores for separately constructed cases. A later
multi-packet/multi-case-in-one-store extension must declare a complete semantic
ID namespace and remap every reference consistently; it is outside this bounded
task.

`probe.transition_for(adapted_day)` now constructs the opportunity from the new
after metadata and time. `probe.ciav_input(transition)` uses that transition's
after time plus one minute. No internal CIAV detection UUID needs to be fabricated
in advance.

## Stream assembly and actual source binding

Reuse `build`'s `OracleProducer`, `ContinuousStateStore` and
`ContinuousEvidenceInput` assembly, with the adapted probe and stream scope `S`.
Include the adapted case/bridge configuration and its pins in the new run's
declared source identity. Preserve the existing action/CIAV utility settings.

One simple admission order is:

1. `stream.admit(delivery.observations,
   received_at=delivery.received_at)` in the new offline replay runtime.
2. Generate each separate synthetic semantic placeholder with the existing
   `raw_for(transition, index)` under its adapted scope and time. Admit it at the
   synthetic step cutoff, set an explicitly controlled `GroundedTransition`,
   and call `advance(cutoff=after.detection_time + 1 minute)`.
3. Publish through `produce_joint_posterior()` with the existing real checkpoint
   wrapper. The archive packet remains raw evidence, not an executed camera
   command owned by this runtime.

The producer configuration binds the predeclared synthetic input detection ID,
the exact original packet, one public candidate and seed, affinity/model pins,
and the paired no-factor flag. Preserve the existing narrow record rule:
match native `after` directly, or native `before` only when the current native
after-record's source is exactly
`structure-two-adaptive-ciav-feedback-closure`. Never search historical records
or consume the first available copy of the image regardless of semantic source.

Save configured input ID, actual native before/after IDs and published revision
ID in the evidence. Withdrawal must remove that **actual published native after
revision**. It is not sufficient to withdraw another event from the same day.
The raw packet can remain in the journal; replay must not move it to a different
retained source. Keep at least one neutral source so native replay retains a
nonempty history. Three steps (one factor source, two neutral sources) suffice
for this bounded engineering check.

## Recovery: fresh SQLite is different from a new run

Persist a validated visible-case JSON, bridge configuration, original packet
binding, model/checkpoint pins, and the fixed CIAV settings. Do not attempt to
serialize the Python context-builder closure.

For a fresh process restoring SQLite:

1. Load and pin-check the same adapted case JSON; reconstruct it with
   `VisibleActionCase.model_validate` and create a new probe holding that case.
2. Recreate the same candidate and `NeuralNativeProducer` with the same original
   packet configuration and external model/checkpoint pins.
3. Recreate the builder according to existing `build`: on every call first assign
   `probe.system = system` and `probe.step_index = step`; then construct the
   `AdaptiveExecutionContext` with the same router/CIAV settings. This ensures
   router features use the restored system, not an unused newly created system.
4. Pass it to `ContinuousEvidenceInput.resume(store, producer=OracleProducer(),
   context_builder=builder, joint_producer=joint)`. Existing native history
   replay uses the stored accepted source bodies and resets the candidate to its
   initial checkpoint. It must not ask the builder to regenerate old CIAV UUIDs.
5. Compare decision view, weights, 6D natural parameters, producer checkpoint,
   retained evidence sources and ledger. An immediate duplicate publish must be
   idempotent and must execute no external action.

Calling `probe.ciav_input` afresh can generate new action/CIAV UUIDs. Therefore a
new process restoring the same SQLite state is **not** evidence that a completely
new run from an empty database reproduces all bytes. For a from-zero rerun, save
and reuse the CIAV input/action journal's UUIDs and configurations, as well as the
input transition journal; restore the named realizer implementation separately.
The existing `build(..., ciav_journal=...)` demonstrates reuse in memory, but the
bridge would need an explicit durable representation if it claims cross-process
from-zero identity. Do not silently compare only numeric outputs and call that
full byte equivalence.

## Strict multi-box archive → single-box correspondence

The current producer accepts one candidate; it need not be expanded to all boxes.
Make its restricted measurement correspond exactly to one original neighborhood:

1. Start from the externally pinned, freshly verified archive readout and its
   original cached public detector candidate artifacts. Predeclare a selection
   rule over frame ordinal, candidate method/ID and pixel seed using only public
   metadata and validity; do not use private masks, reference positions or
   validation error. Preserve unavailable selections as failures if the fixed
   rule yields none.
2. Require exact equality of the selected candidate's method, UUID and all four
   box values to the original candidate. Do not use approximate box overlap as
   the correspondence criterion.
3. Recompute its canonical 8×8 deduplicated pixel grid from the exact box and the
   original image dimensions. Require complete equality to one neighborhood's
   `pixels_uv` in the full archive readout, and require that neighborhood's
   `sources` contains the selected candidate. A duplicate candidate from another
   frontend may share this full grid; preserve that provenance without counting
   another measurement.
4. Recompute the one-candidate readout from the same original RGB-D/self-pose and
   the same pinned affinity model. Compare the complete grid's validity, world
   points and the chosen seed's raw and normalized soft/uniform coefficient
   rows and representative points to the original neighborhood. Any numeric
   tolerance must be declared solely as a floating-point comparison tolerance,
   not a scientific acceptance/calibration threshold. Checking only final XYZ
   is insufficient: different supports can have the same mean.
5. Bind the correspondence in a dedicated bridge receipt. At minimum include
   original capture/inventory pin and packet binding; original full-readout pin,
   input/neighborhood/seed IDs; exact candidate and seed pixel; canonical grid
   and its digest; one-candidate readout input/seed IDs; affinity, estimator and
   residual-model pins; and the complete correspondence-check results.

The single-box and full-frame `input_sha256` values include different candidate
sets. Their provenance `source_sha256` definitions also differ between the
archive dataset owner and packet-bound native producer. Consequently seed and
measurement IDs can legitimately differ even when the pixel neighborhood and
numeric readout are identical. **Do not overwrite either ID to force equality.**
The bridge receipt explicitly relates the two source-bound representations.
Nor should different IDs alone be used to justify counting the same original
packet/grid/seed twice.

## Minimum next implementation evidence

- Exact original raw equality/pins before and after admission; no invented camera
  command registration or dispatch.
- Single-box/full-neighborhood correspondence from original candidates and raw
  pixels, including a complete mismatched-grid/candidate rejection.
- Actual native pre-update likelihood, target weights and full 6D state change,
  with known/unknown/aggregate assumptions fixed and disclosed.
- Duplicate/later-source non-reuse; withdrawal of the actual bound source;
  complete replay to the paired no-factor baseline; fresh SQLite restore.
- Complete public-packet/source/bridge-receipt forgery rejected, followed by a
  valid recovery path. Recomputed hashes alone cannot replace external pins.

Freeze the implementation, then run the required two sequential adversarial
reviews before executing and reporting the real archive bridge. This design
document does not confer natural identity or scientific likelihood authority.
